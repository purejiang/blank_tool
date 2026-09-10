<template>
  <div v-show="active" class="result-panel">
  <div class="result-block" v-if="runResult || liveSteps.length">
    <div class="result-summary">
      <n-tag v-if="runResult" :type="runResult.cancelled ? 'warning' : (runResult.success ? 'success' : 'error')" size="small">
        {{ runResult.cancelled ? t('automation.cancelled') : (runResult.success ? t('automation.success') : t('automation.failed')) }}
      </n-tag>
      <n-tag v-else type="info" size="small">{{ t('automation.running') }}</n-tag>
      <span class="sum-item">{{ t('automation.total') }}: {{ runResult ? (runResult.total ?? 0) : stepRows.length }}</span>
      <span class="sum-item ok">{{ t('automation.passed') }}: {{ stepPassed }}</span>
      <span class="sum-item bad">{{ t('automation.failed') }}: {{ stepFailed }}</span>
    </div>

    <div class="crash-note" v-if="runResult?.aborted_by_crash">
      <span class="crash-text">{{ t('automation.crashAborted') }}</span>
      <span v-if="runResult?.crash_log" class="crash-log">{{ t('automation.crashLog') }}: {{ runResult.crash_log }}</span>
    </div>

    <div class="crash-note" v-if="runResult?.traffic_log">
      <span class="crash-text">{{ t('automation.trafficRequests') }}: {{ runResult.traffic_requests ?? 0 }}</span>
      <span class="crash-log">{{ t('automation.trafficLog') }}: {{ runResult.traffic_log }}</span>
    </div>

    <div class="steps-result" ref="stepsScroll">
      <div v-for="st in stepRows" :key="st.index" class="step-line" :class="stepRowClass(st)">
        <span class="step-idx">#{{ st.index }}</span>
        <span class="step-act">{{ actLabel(st.action) }}</span>
        <span class="step-msg">{{ st.pending ? t('automation.stepPending') : (st.message || (st.ok ? 'ok' : 'fail')) }}</span>
        <span class="step-dur" v-if="st.duration_ms">{{ st.duration_ms }}ms</span>
      </div>
    </div>

    <div class="shots" v-if="screenshots.length">
      <div class="shots-title">{{ t('automation.screenshots') }}</div>
      <div class="shot-grid">
        <n-image
          v-for="(sp, i) in screenshots"
          :key="i"
          :src="fileUrl(sp)"
          width="96"
          height="170"
          object-fit="cover"
          :alt="sp"
        />
      </div>
    </div>
  </div>
  <n-empty v-else :description="t('automation.noResult')" size="small" class="col-empty" />

  <div class="log-head">{{ t('automation.runLog') }}</div>
  <n-scrollbar class="log-scroll" ref="logScroll">
    <pre class="log-box">{{ logsText }}</pre>
  </n-scrollbar>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { NTag, NImage, NEmpty, NScrollbar } from 'naive-ui'
import { stepActionLabel } from '@components/automation/stepMeta'

const props = defineProps<{
  active: boolean
  running: boolean
  runResult: any
  liveSteps: any[]
  screenshots: string[]
  logs: string[]
}>()

const { t } = useI18n()

/** 结果区渲染源：运行中/结束后优先用实时行，无则回落到 complete 载荷 */
const stepRows = computed(() => {
  if (props.liveSteps.length) return props.liveSteps
  return props.runResult?.steps || []
})
const stepPassed = computed(() => stepRows.value.filter((s: any) => s.ok === true).length)
const stepFailed = computed(() => stepRows.value.filter((s: any) => s.ok === false).length)

function stepRowClass(st: any) {
  if (st.pending) return 'pending'
  return st.ok ? 'ok' : 'bad'
}

function actLabel(action: string): string {
  return stepActionLabel(action, t)
}

function fileUrl(p: string): string {
  if (!p) return ''
  if (p.startsWith('file://')) return p
  return 'file:///' + p.replace(/\\/g, '/')
}

const logsText = computed(() => props.logs.join('\n'))

// auto-scroll refs (DOM anchors live in this component)
const logScroll = ref<any>(null)
const stepsScroll = ref<HTMLElement | null>(null)

// auto-scroll step results to bottom as rows stream in
watch(
  () => props.liveSteps.length,
  async () => {
    await nextTick()
    const el = stepsScroll.value
    if (el) el.scrollTop = el.scrollHeight
  },
)

// auto-scroll log to bottom
watch(
  () => props.logs.length,
  async () => {
    await nextTick()
    const inst = logScroll.value?.instRef
    const el = inst?.$el as HTMLElement | undefined
    if (el) el.scrollTop = el.scrollHeight
  },
)
</script>

<style scoped>
.result-panel { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.col-empty { margin: auto; text-align: center; }
.result-block { flex: 0 0 auto; }
.result-summary { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 8px; }
.sum-item { font-size: 12px; color: var(--app-text-secondary); }
.sum-item.ok { color: #18a058; }
.sum-item.bad { color: #d03050; }
.crash-note { display: flex; flex-direction: column; gap: 2px; font-size: 12px; margin: 6px 0; }
.crash-text { color: #d03050; font-weight: 600; }
.crash-log { color: var(--app-text-muted); word-break: break-all; }
.steps-result { max-height: 200px; overflow: auto; border: 1px solid var(--app-card-border); border-radius: 8px; padding: 6px; }
.step-line { display: flex; gap: 8px; align-items: baseline; font-size: 12px; padding: 2px 0; border-bottom: 1px dashed var(--app-card-border); }
.step-line.ok .step-idx { color: #18a058; }
.step-line.bad .step-idx { color: #d03050; }
.step-line.pending .step-idx { color: #2080f0; }
.step-line.pending .step-msg { color: #2080f0; font-style: italic; }
.step-idx { font-weight: 600; }
.step-act { color: var(--app-text-primary); font-weight: 500; }
.step-msg { color: var(--app-text-muted); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.step-dur { color: var(--app-text-muted); font-size: 11px; }
.shots { margin-top: 10px; }
.shots-title { font-size: 12px; color: var(--app-text-secondary); margin-bottom: 6px; }
.shot-grid { display: flex; flex-wrap: wrap; gap: 6px; }
.log-head { font-size: 12px; color: var(--app-text-muted); margin: 12px 0 4px; }
.log-scroll { flex: 1; min-height: 120px; border: 1px solid var(--app-card-border); border-radius: 8px; background: #0f1115; }
.log-box {
  margin: 0; padding: 10px; color: #c8d0da; font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 11.5px; line-height: 1.5; white-space: pre-wrap; word-break: break-all;
}
</style>
