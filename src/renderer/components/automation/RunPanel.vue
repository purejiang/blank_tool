<template>
  <div class="run-panel">
    <!-- ============ status bar (one line, replaces the old title + summary
         + report-button + run-dir rows) ============ -->
    <!-- NOTE: this bar is `.run-status`, deliberately NOT `.status-bar` —
         main.css styles `.status-bar` globally for the app footer
         (height:100% + space-between). A scoped rule only wins for the
         properties it declares, so the global `height: 100%` silently
         stretched this bar across the whole panel and pushed the tabs +
         steps/logs out of the clipped area. -->
    <div class="run-status" :class="statusClass">
      <span class="dot" />
      <span class="st-label">{{ statusLabel }}</span>
      <span class="st-meta" v-if="!idle">
        <span>{{ src.passed }}/{{ src.total }}</span>
        <span class="sep">·</span>
        <span>{{ fmtDur(src.durationMs) }}</span>
        <template v-if="shotCount">
          <span class="sep">·</span>
          <span>{{ t('automation.shotCountLabel', { n: shotCount }) }}</span>
        </template>
        <template v-if="src.trafficTotal">
          <span class="sep">·</span>
          <span>{{ t('automation.fRequests') }} {{ src.trafficTotal }}</span>
        </template>
      </span>

      <div class="st-acts">
        <n-popover v-if="hasDetails" trigger="click" placement="bottom-end" :show-arrow="false">
          <template #trigger>
            <n-button size="tiny" text>{{ t('automation.details') }}</n-button>
          </template>
          <div class="detail-pop">
            <div class="dp-row" v-if="src.runDir">
              <span class="dp-k">{{ t('automation.runDir') }}</span>
              <span class="dp-v path" :title="src.runDir" @click="copyText(src.runDir, 'runDir')">
                {{ copied === 'runDir' ? t('automation.copied') : src.runDir }}
              </span>
            </div>
            <div class="dp-row" v-if="src.deviceId">
              <span class="dp-k">{{ t('automation.device') }}</span>
              <span class="dp-v">{{ src.deviceId }}</span>
            </div>
            <div class="dp-row" v-if="src.packageName">
              <span class="dp-k">{{ t('automation.packageLabel') }}</span>
              <span class="dp-v">{{ src.packageName }}</span>
            </div>
            <div class="dp-row" v-if="src.startedAt">
              <span class="dp-k">{{ t('automation.duration') }}</span>
              <span class="dp-v">{{ src.startedAt }} → {{ src.finishedAt }}</span>
            </div>
            <div class="dp-row" v-if="src.trafficLog">
              <span class="dp-k">{{ t('automation.trafficFile') }}</span>
              <span class="dp-v path" :title="src.trafficLog" @click="copyText(src.trafficLog, 'traffic')">
                {{ copied === 'traffic' ? t('automation.copied') : src.trafficLog }}
              </span>
            </div>
            <div class="dp-row" v-if="src.crashLog">
              <span class="dp-k">{{ t('automation.crashLog') }}</span>
              <span class="dp-v path" :title="src.crashLog" @click="copyText(src.crashLog, 'crash')">
                {{ copied === 'crash' ? t('automation.copied') : src.crashLog }}
              </span>
            </div>
          </div>
        </n-popover>
      </div>
    </div>

    <!-- crash is exceptional — stays inline instead of hiding in 详情 -->
    <div class="crash-note" v-if="src.abortedByCrash">
      <span class="crash-text">{{ t('automation.crashAborted') }}</span>
      <span v-if="src.crashLog" class="crash-log">{{ src.crashLog }}</span>
    </div>

    <!-- ============ tabs: steps / requests / logs share ONE block;
         report actions live on the right of this row so the status
         bar stays a single calm line ============ -->
    <div class="tabs">
      <button
        v-for="tb in tabs" :key="tb.key" type="button"
        class="tab" :class="{ on: tab === tb.key }"
        @click="tab = tb.key"
      >
        {{ tb.label }}<span v-if="tb.count" class="tab-n">{{ tb.count }}</span>
      </button>
      <div class="tabs-acts">
        <span v-if="tab === 'logs' && logs.length" class="only-err">
          <n-checkbox v-model:checked="onlyErrors" size="small">{{ t('automation.onlyErrors') }}</n-checkbox>
        </span>
        <n-button v-if="src.taskId && !running" size="tiny" :loading="exporting" @click="emit('open-file')">
          <template #icon><n-icon size="13"><ExternalLink /></n-icon></template>
          {{ t('automation.openInBrowser') }}
        </n-button>
        <n-button v-if="src.taskId && !running" size="tiny" @click="emit('download-report')">
          <template #icon><n-icon size="13"><Download /></n-icon></template>
          {{ t('automation.downloadReport') }}
        </n-button>
        <n-button v-if="isReport" size="tiny" text :title="t('common.close')" @click="emit('close-report')">
          <template #icon><n-icon size="13"><X /></n-icon></template>
        </n-button>
      </div>
    </div>

    <div class="panel-body">
      <!-- ---- steps ---- -->
      <div v-if="tab === 'steps'" class="scroll">
        <div v-if="!stepsWithShots.length" class="empty">{{ t('automation.noResult') }}</div>
        <div v-for="st in stepsWithShots" :key="st.index" class="step-block">
          <div class="srow" :class="rowClass(st)" @click="toggle(st.index)">
            <span class="s-rel">{{ relText(st) }}</span>
            <span class="s-idx">#{{ st.index }}</span>
            <span class="s-act">{{ actLabel(st.action) }}</span>
            <span class="s-msg">{{ st.pending ? t('automation.stepPending') : (st.message || (st.ok ? 'ok' : 'fail')) }}</span>
            <span v-if="st.shots.length" class="s-shots" :title="t('automation.shotCountLabel', { n: st.shots.length })">
              <n-icon size="12"><ImageIcon /></n-icon>{{ st.shots.length }}
            </span>
            <span class="s-dur" v-if="st.duration_ms">{{ fmtDur(st.duration_ms) }}</span>
          </div>
          <div v-if="expanded === st.index" class="sdetail">
            <div class="sd-msg">{{ st.message || (st.ok ? 'ok' : 'fail') }}</div>
            <div v-if="st.shots.length" class="sd-shots">
              <n-image
                v-for="(p, k) in st.shots" :key="k"
                :src="fileUrl(p)" width="64" height="114" object-fit="cover" :alt="p"
                :preview-src="fileUrl(p)"
              />
            </div>
            <div v-else class="sd-empty">{{ t('automation.noShots') }}</div>
          </div>
        </div>
      </div>

      <!-- ---- requests ---- -->
      <div v-else-if="tab === 'requests'" class="scroll">
        <div v-if="!requests.length" class="empty">
          {{ isReport ? t('automation.noRequests') : t('automation.requestsLiveHint') }}
        </div>
        <div v-else class="req-list">
          <div v-for="(rq, i) in requests" :key="i" class="req-row" :class="reqClass(rq)">
            <span class="req-t">{{ reqRel(rq.ts) }}</span>
            <span class="req-m">{{ rq.method }}</span>
            <span class="req-s">{{ rq.status ?? (rq.error ? 'ERR' : '-') }}</span>
            <span class="req-u" :title="rq.url">{{ rq.url }}</span>
          </div>
          <div v-if="src.truncated" class="trunc-note">
            {{ t('automation.trafficTruncated', { n: src.trafficTotal }) }}
          </div>
        </div>
      </div>

      <!-- ---- logs ---- -->
      <div v-else class="scroll log-scroll" ref="logEl">
        <div v-if="!visibleLogs.length" class="empty">
          {{ logs.length ? t('automation.noErrorLines') : t('automation.noLogs') }}
        </div>
        <div v-for="(l, i) in visibleLogs" :key="i" class="log-line" :class="l.level">
          <span class="ll-ts">{{ logTime(l.ts) }}</span>
          <span class="ll-text">{{ l.body }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NCheckbox, NIcon, NImage, NPopover } from 'naive-ui'
import { Download, ExternalLink, Image as ImageIcon, X } from 'lucide-vue-next'
import { stepActionLabel } from '@components/automation/stepMeta'

const props = defineProps<{
  running: boolean
  runResult: any
  liveSteps: any[]
  /** live console lines (renderer clock, epoch seconds) */
  logs: { ts: number; text: string }[]
  screenshots: string[]
  /** run start (renderer clock, epoch seconds) — baseline for the live log tab */
  runStartedTs: number
  /** set when replaying a historical run (read_run payload); null = live view */
  report?: any | null
  exporting?: boolean
}>()

const emit = defineEmits<{
  (e: 'open-file'): void
  (e: 'download-report'): void
  (e: 'close-report'): void
}>()

const { t } = useI18n()

const isReport = computed(() => !!props.report)
const tab = ref<'steps' | 'requests' | 'logs'>('steps')
const onlyErrors = ref(false)
const expanded = ref<number | null>(null)
const copied = ref('')

// ---------------------------------------------------------------- source --
// One normalized view for both the live console and a replayed report, so
// the two modes render identically instead of swapping whole layouts.
const src = computed(() => {
  if (props.report) {
    const r = props.report
    return {
      steps: r.steps || [],
      logs: r.logs || [],
      shots: r.screenshots || [],
      shotsMeta: r.shots_meta || [],
      requests: r.traffic || [],
      trafficTotal: r.traffic_total ?? 0,
      truncated: !!r.traffic_truncated,
      startedTs: Number(r.started_ts) || 0,
      startedAt: r.started_at || '',
      finishedAt: r.finished_at || '',
      durationMs: Number(r.duration_ms) || 0,
      total: r.total ?? 0,
      passed: r.passed ?? 0,
      failed: r.failed ?? 0,
      cancelled: !!r.cancelled,
      success: !!r.success,
      crashLog: r.crash_log || '',
      trafficLog: r.traffic_log || '',
      runDir: r.run_dir || '',
      packageName: r.package_name || '',
      deviceId: r.device_id || '',
      abortedByCrash: !!r.aborted_by_crash,
      taskId: r.task_id || '',
    }
  }
  const res = props.runResult || {}
  const st = (props.liveSteps || []) as any[]
  const tss = st.map(s => Number(s.started_at)).filter(n => n > 0)
  const ends = st.map(s => Number(s.ended_at)).filter(n => n > 0)
  return {
    steps: st,
    logs: props.logs || [],
    shots: res.screenshots || props.screenshots || [],
    shotsMeta: res.shots_meta || [],
    requests: [] as any[],
    trafficTotal: res.traffic_requests ?? 0,
    truncated: false,
    startedTs: props.runStartedTs || 0,
    startedAt: fmtClock(props.runStartedTs),
    finishedAt: res.task_id ? fmtClock(Date.now() / 1000) : '',
    durationMs: tss.length && ends.length ? Math.round((Math.max(...ends) - Math.min(...tss)) * 1000) : 0,
    total: res.total ?? st.length,
    passed: res.passed ?? st.filter(s => s.ok === true).length,
    failed: res.failed ?? st.filter(s => s.ok === false).length,
    cancelled: !!res.cancelled,
    success: !!res.success,
    crashLog: res.crash_log || '',
    trafficLog: res.traffic_log || '',
    runDir: res.run_dir || '',
    packageName: res.package_name || '',
    deviceId: '',
    abortedByCrash: !!res.aborted_by_crash,
    taskId: res.task_id || '',
  }
})

const steps = computed(() => src.value.steps)
/** 请求列表只有回放历史运行时才有（实时流不推送抓包明细） */
const requests = computed(() => src.value.requests || [])

/** Nothing has run yet — the status bar shows a neutral hint instead of 0/0. */
const idle = computed(() =>
  !props.running && !isReport.value && !src.value.taskId && !steps.value.length
)

/** Timeline anchor: the report's start (same clock as its timestamps), or —
 *  in live mode — the first step seen. Never mix renderer and backend clocks
 *  inside one tab. */
const baseline = computed(() => {
  if (isReport.value) return src.value.startedTs || 0
  const tss = (props.liveSteps || []).map((s: any) => Number(s.started_at)).filter((n: number) => n > 0)
  return tss.length ? Math.min(...tss) : 0
})

function relText(st: any): string {
  if (st.pending) return '—'
  return rel(st.started_at)
}

function rel(ts: any): string {
  const v = Number(ts)
  const b = baseline.value
  if (!Number.isFinite(v) || v <= 0 || !b) return '—'
  const d = v - b
  return d < 0 ? '—' : `+${d.toFixed(2)}s`
}

function reqRel(ts: any): string {
  return rel(ts)
}

// ------------------------------------------------------------------ shots --
/** per-step screenshots: the step's own shot + shots_meta entries for it */
function shotsFor(index: number): string[] {
  const out: string[] = []
  const own = steps.value.find((s: any) => s.index === index)?.screenshot
  if (own) out.push(own)
  for (const m of src.value.shotsMeta || []) {
    if (Number(m?.step_index) === index && m?.path && !out.includes(m.path)) out.push(m.path)
  }
  return out
}

const stepsWithShots = computed(() =>
  steps.value.map((s: any) => ({ ...s, shots: shotsFor(s.index) }))
)

const shotCount = computed(() => {
  const set = new Set<string>(src.value.shots || [])
  for (const s of stepsWithShots.value) for (const p of s.shots) set.add(p)
  return set.size
})

// ------------------------------------------------------------------- logs --
/** `[adb_auto] msg` → level + body. The plugin tag is noise; level words
 *  ([FAIL]/[ERROR]/[WARN]/[CANCELLED]) are what the eye needs to catch. */
function normalizeLog(text: string) {
  let body = String(text)
  let level: 'error' | 'warn' | 'info' = 'info'
  if (/\[(FAIL|ERROR)\]/i.test(body)) level = 'error'
  else if (/\[(WARN|CANCEL)/i.test(body)) level = 'warn'
  const m = /^\[([A-Za-z_][\w.\-]*)\]\s+([\s\S]*)$/.exec(body)
  if (m && !/^(FAIL|ERROR|WARN|CANCEL)/i.test(m[1])) body = m[2]
  return { ts: 0, body, level }
}

const logs = computed(() => (src.value.logs || []).map((l: any) => {
  const n = normalizeLog(l?.text ?? l ?? '')
  return { ...n, ts: Number(l?.ts) || 0 }
}))

const errCount = computed(() => logs.value.filter(l => l.level === 'error').length)
const visibleLogs = computed(() => (onlyErrors.value ? logs.value.filter(l => l.level === 'error') : logs.value))

function logTime(ts: number): string {
  if (!ts) return '—'
  const base = isReport.value ? (src.value.startedTs || ts) : (props.runStartedTs || ts)
  const d = ts - base
  return d < 0 ? fmtClock(ts) : `+${d.toFixed(2)}s`
}

// ------------------------------------------------------------------ tabs ---
const tabs = computed(() => [
  { key: 'steps' as const, label: t('automation.fSteps'), count: steps.value.length },
  { key: 'requests' as const, label: t('automation.fRequests'), count: src.value.requests.length || src.value.trafficTotal },
  { key: 'logs' as const, label: t('automation.tabLogs'), count: logs.value.length },
])

// Switching to a different run (or a new one) resets the transient UI state
// and lands on the steps tab (default per user preference); the log tab is
// one click away while a run is in progress.
watch(
  () => [src.value.taskId, isReport.value].join('|'),
  () => {
    expanded.value = null
    onlyErrors.value = false
    tab.value = 'steps'
  },
  { immediate: true },
)
// When a run ends without any logs (e.g. failed before starting), an open
// log tab would just show emptiness — fall back to steps.
watch(() => props.running, (v) => {
  if (v) {
    expanded.value = null
  } else if (tab.value === 'logs' && !logs.value.length) {
    tab.value = 'steps'
  }
})

// ------------------------------------------------------------------- misc --
const statusClass = computed(() => {
  if (idle.value) return 'idle'
  if (props.running) return 'run'
  if (src.value.cancelled) return 'warn'
  return src.value.success ? 'ok' : 'bad'
})

const statusLabel = computed(() => {
  if (idle.value) return t('automation.noResult')
  if (props.running) return t('automation.running')
  if (src.value.cancelled) return t('automation.cancelled')
  return src.value.success ? t('automation.success') : t('automation.failed')
})

const hasDetails = computed(() =>
  !!(src.value.runDir || src.value.trafficLog || src.value.crashLog || src.value.deviceId)
)

function rowClass(st: any) {
  if (st.pending) return 'pending'
  return st.ok ? 'ok' : 'bad'
}

function actLabel(action: string): string {
  return stepActionLabel(action, t)
}

function fmtDur(ms: any): string {
  const n = Number(ms) || 0
  return n >= 1000 ? `${(n / 1000).toFixed(1)}s` : `${n}ms`
}

function fmtClock(ts: any): string {
  const v = Number(ts)
  if (!Number.isFinite(v) || v <= 0) return ''
  const d = new Date(v * 1000)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function reqClass(rq: any): string {
  if (rq?.error) return 'bad'
  const c = rq?.status
  if (typeof c !== 'number') return 'bad'
  return c < 400 ? 'ok' : 'warn'
}

function fileUrl(p: string): string {
  if (!p) return ''
  if (p.startsWith('file://') || p.startsWith('data:')) return p
  return 'file:///' + p.replace(/\\/g, '/')
}

function toggle(index: number) {
  expanded.value = expanded.value === index ? null : index
}

async function copyText(text: string, key: string) {
  try {
    await navigator.clipboard.writeText(text)
    copied.value = key
    setTimeout(() => { if (copied.value === key) copied.value = '' }, 1500)
  } catch {
    /* clipboard unavailable — the path is still selectable in the DOM */
  }
}

// auto-scroll the log feed
const logEl = ref<HTMLElement | null>(null)
watch(visibleLogs, async () => {
  await nextTick()
  const el = logEl.value
  if (el) el.scrollTop = el.scrollHeight
})
</script>

<style scoped>
.run-panel { display: flex; flex-direction: column; flex: 1 1 auto; min-height: 0; overflow: hidden; }

/* ---- status bar ---- */
.run-status {
  display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px;
  padding: 7px 9px; border-radius: 8px;
  border: 1px solid var(--app-card-border);
  background: var(--app-card-bg);
  flex: none;
}
.dot { width: 7px; height: 7px; border-radius: 50%; flex: none; background: var(--app-text-muted); }
.run-status.idle .st-label { color: var(--app-text-muted); font-weight: 400; }
.run-status.ok .dot { background: #18a058; }
.run-status.bad .dot { background: #d03050; }
.run-status.warn .dot { background: #f0a020; }
.run-status.run .dot { background: #2080f0; }
.st-label { font-size: 12px; font-weight: 600; flex: none; }
.run-status.ok .st-label { color: #18a058; }
.run-status.bad .st-label { color: #d03050; }
.run-status.warn .st-label { color: #f0a020; }
.run-status.run .st-label { color: #2080f0; }
.st-meta { font-size: 11.5px; color: var(--app-text-secondary); flex: 1; min-width: 0; }
.st-meta .sep { color: var(--app-text-muted); margin: 0 3px; }
.st-acts { display: flex; align-items: center; gap: 4px; flex: none; margin-left: auto; }

/* ---- details popover ---- */
.detail-pop { display: flex; flex-direction: column; gap: 6px; max-width: 320px; }
.dp-row { display: flex; gap: 8px; font-size: 11.5px; align-items: baseline; }
.dp-k { flex: none; color: var(--app-text-muted); min-width: 62px; }
.dp-v { color: var(--app-text-secondary); word-break: break-all; }
.dp-v.path { cursor: copy; }
.dp-v.path:hover { color: #2080f0; }

.crash-note { display: flex; flex-direction: column; gap: 2px; font-size: 12px; margin-top: 6px; flex: none; }
.crash-text { color: #d03050; font-weight: 600; }
.crash-log { color: var(--app-text-muted); word-break: break-all; }

/* ---- tabs ---- */
.tabs {
  display: flex; align-items: center; gap: 2px;
  margin-top: 8px; flex: none;
  border-bottom: 1px solid var(--app-card-border);
}
.tab {
  appearance: none; background: none; border: none; cursor: pointer;
  padding: 5px 10px; font-size: 12px; color: var(--app-text-muted);
  border-bottom: 2px solid transparent; margin-bottom: -1px;
  font-family: inherit; display: flex; align-items: center; gap: 5px;
}
.tab:hover { color: var(--app-text-primary); }
.tab.on { color: #2080f0; font-weight: 600; border-bottom-color: #2080f0; }
.tab-n {
  font-size: 10.5px; font-weight: 400; color: var(--app-text-muted);
  background: var(--app-blue-bg); border-radius: 8px; padding: 0 5px; line-height: 15px;
}
.only-err { display: flex; align-items: center; padding-bottom: 2px; }
/* report actions live on the tabs row, right-aligned; bottom padding
   keeps their hit area above the tab underline */
.tabs-acts {
  margin-left: auto; display: flex; align-items: center; gap: 5px;
  padding-bottom: 3px; flex: none;
}

/* ---- panel body ---- */
.panel-body { flex: 1 1 auto; min-height: 0; overflow: hidden; display: flex; flex-direction: column; margin-top: 6px; }
/* min-height MUST stay 0: any floor here makes the list outgrow the panel and
   paint over the run history underneath it */
.scroll { flex: 1 1 auto; min-height: 0; overflow: auto; }
.empty { padding: 18px 8px; text-align: center; color: var(--app-text-muted); font-size: 12px; }

/* ---- step rows ---- */
.step-block + .step-block { border-top: 1px dashed var(--app-card-border); }
.srow {
  display: flex; gap: 7px; align-items: baseline;
  padding: 4px 2px; font-size: 12px; cursor: pointer; border-radius: 5px;
}
.srow:hover { background: var(--app-blue-bg); }
.s-rel { flex: none; width: 48px; font-size: 10.5px; color: var(--app-text-muted); font-variant-numeric: tabular-nums; }
.s-idx { flex: none; font-weight: 600; color: var(--app-text-muted); }
.srow.ok .s-idx { color: #18a058; }
.srow.bad .s-idx { color: #d03050; }
.srow.pending .s-idx { color: #2080f0; }
.s-act { flex: none; color: var(--app-text-primary); font-weight: 500; }
.s-msg { flex: 1; min-width: 0; color: var(--app-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.srow.pending .s-msg { color: #2080f0; font-style: italic; }
.s-shots {
  flex: none; display: flex; align-items: center; gap: 2px;
  font-size: 10.5px; color: var(--app-text-muted);
  background: var(--app-blue-bg); border-radius: 6px; padding: 0 5px;
}
.s-dur { flex: none; font-size: 10.5px; color: var(--app-text-muted); font-variant-numeric: tabular-nums; }
.sdetail {
  margin: 0 0 6px 55px; padding: 6px 8px;
  background: var(--app-blue-bg); border-radius: 6px;
}
.sd-msg { font-size: 11.5px; color: var(--app-text-secondary); word-break: break-all; }
.sd-shots { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 6px; }
.sd-empty { font-size: 11px; color: var(--app-text-muted); margin-top: 4px; }

/* ---- requests ---- */
.req-list { display: flex; flex-direction: column; }
.req-row { display: flex; gap: 7px; align-items: baseline; font-size: 11.5px; padding: 2px 0; }
.req-row.ok .req-s { color: #18a058; }
.req-row.warn .req-s { color: #f0a020; }
.req-row.bad .req-s { color: #d03050; }
.req-t { flex: none; width: 50px; color: var(--app-text-muted); font-variant-numeric: tabular-nums; font-size: 10.5px; }
.req-m { flex: none; width: 48px; font-weight: 600; color: var(--app-text-primary); }
.req-s { flex: none; width: 32px; }
.req-u { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--app-text-muted); }
.trunc-note { font-size: 11px; color: #f0a020; padding: 6px 0; }

/* ---- logs ---- */
.log-scroll { background: #0f1115; border: 1px solid var(--app-card-border); border-radius: 8px; padding: 6px 8px; }
.log-line { display: flex; gap: 8px; font-family: 'SFMono-Regular', Consolas, monospace; font-size: 11.5px; line-height: 1.55; }
.ll-ts { flex: none; width: 46px; color: #5c6672; font-variant-numeric: tabular-nums; }
.ll-text { flex: 1; min-width: 0; color: #c8d0da; white-space: pre-wrap; word-break: break-all; }
.log-line.error .ll-text { color: #ff7a85; }
.log-line.error .ll-ts { color: #8a4a52; }
.log-line.warn .ll-text { color: #f0c060; }
.log-scroll .empty { color: #5c6672; }
</style>
