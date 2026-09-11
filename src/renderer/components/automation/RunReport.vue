<template>
  <div class="run-report">
    <!-- header -->
    <div class="rp-head">
      <n-tag
        size="small"
        :bordered="false"
        :type="report.cancelled ? 'warning' : (report.success ? 'success' : 'error')"
      >
        {{ report.cancelled ? t('automation.cancelled') : (report.success ? t('automation.success') : t('automation.failed')) }}
      </n-tag>
      <span class="rp-title">{{ t('automation.reportTitle') }}</span>
      <span class="rp-meta">{{ report.task_id }}</span>
      <div class="rp-ops">
        <n-button size="tiny" :loading="exporting" @click="emit('export')">
          <template #icon><n-icon><Download /></n-icon></template>
          {{ t('automation.exportReport') }}
        </n-button>
        <n-button size="tiny" text :title="t('common.close')" @click="emit('close')">
          <template #icon><n-icon><X /></n-icon></template>
        </n-button>
      </div>
    </div>

    <!-- summary -->
    <div class="rp-sum">
      <span class="s-item">{{ report.started_at }} → {{ report.finished_at }}</span>
      <span class="s-item">{{ t('automation.duration') }}: {{ fmtDur(report.duration_ms) }}</span>
      <span class="s-item">{{ t('automation.total') }}: {{ report.total ?? 0 }}</span>
      <span class="s-item ok">{{ t('automation.passed') }}: {{ report.passed ?? 0 }}</span>
      <span class="s-item bad">{{ t('automation.failed') }}: {{ report.failed ?? 0 }}</span>
      <span class="s-item">{{ t('automation.trafficRequests') }}: {{ report.traffic_total ?? 0 }}</span>
      <span class="s-item">{{ t('automation.screenshots') }}: {{ shotCount }}</span>
      <span class="s-item pkg" v-if="report.package_name">{{ report.package_name }}</span>
    </div>

    <div class="crash-note" v-if="report.aborted_by_crash">
      <span class="crash-text">{{ t('automation.crashAborted') }}</span>
      <span v-if="report.crash_log" class="crash-log">{{ report.crash_log }}</span>
    </div>

    <!-- filters -->
    <div class="rp-filters">
      <n-checkbox v-model:checked="showSteps" size="small">{{ t('automation.fSteps') }} ({{ stepRows.length }})</n-checkbox>
      <n-checkbox v-model:checked="showReqs" size="small">{{ t('automation.fRequests') }} ({{ traffic.length }})</n-checkbox>
      <n-checkbox v-model:checked="showShots" size="small">{{ t('automation.fScreenshots') }} ({{ shotCount }})</n-checkbox>
      <span class="rp-hint">{{ t('automation.timelineHint') }}</span>
    </div>

    <!-- unified timeline -->
    <n-scrollbar class="tl-scroll">
      <div v-if="!timeline.length" class="tl-empty">{{ t('automation.noTimeline') }}</div>
      <div
        v-for="(it, i) in timeline"
        :key="i"
        class="tl-row"
        :class="it.kind"
      >
        <span class="tl-rel">{{ fmtRel(it.rel) }}</span>
        <span class="tl-kind">
          <n-tag
            size="tiny"
            :bordered="false"
            :type="it.kind === 'step'
              ? (it.ok ? 'success' : 'error')
              : (typeof it.status === 'number' ? (it.status < 400 ? 'success' : 'warning') : 'error')"
          >
            {{ it.kind === 'step' ? `#${it.index} ${it.title}` : it.method }}
          </n-tag>
        </span>
        <span class="tl-body">
          <span class="tl-main" :title="it.kind === 'step' ? it.detail : it.url">
            {{ it.kind === 'step' ? (it.detail || (it.ok ? 'ok' : 'fail')) : it.url }}
          </span>
          <span v-if="it.kind === 'req'" class="tl-code">{{ it.status ?? '-' }}</span>
          <span v-else-if="it.dur" class="tl-code">{{ fmtDur(it.dur) }}</span>
          <span v-if="it.kind === 'step' && it.shots.length && showShots" class="tl-shots">
            <n-image
              v-for="(sp, k) in it.shots"
              :key="k"
              :src="fileUrl(sp)"
              width="52"
              height="92"
              object-fit="cover"
              :alt="sp"
            />
          </span>
        </span>
      </div>
    </n-scrollbar>

    <!-- screenshot gallery -->
    <template v-if="showShots && shots.length">
      <div class="rp-sec">{{ t('automation.screenshots') }}</div>
      <div class="shot-grid">
        <n-image
          v-for="(sp, i) in shots"
          :key="i"
          :src="fileUrl(sp)"
          width="82"
          height="146"
          object-fit="cover"
          :alt="sp"
          :preview-src="fileUrl(sp)"
        />
      </div>
    </template>

    <!-- request list -->
    <template v-if="showReqs && traffic.length">
      <div class="rp-sec">
        {{ t('automation.requestLog') }}
        <span v-if="report.traffic_truncated" class="rp-warn">
          {{ t('automation.trafficTruncated', { n: report.traffic_total }) }}
        </span>
      </div>
      <div class="req-list">
        <div v-for="(rq, i) in traffic" :key="i" class="req-row" :class="reqClass(rq)">
          <span class="req-t">{{ fmtRel(relOf(rq.ts)) }}</span>
          <span class="req-m">{{ rq.method }}</span>
          <span class="req-s">{{ rq.status ?? (rq.error ? 'ERR' : '-') }}</span>
          <span class="req-u" :title="rq.url">{{ rq.url }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton, NCheckbox, NIcon, NImage, NScrollbar, NTag,
} from 'naive-ui'
import { Download, X } from 'lucide-vue-next'

const props = defineProps<{
  /** report object from automation.read_run (report.json + traffic[]) */
  report: any
  exporting?: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'export'): void
}>()

const { t } = useI18n()

const showSteps = ref(true)
const showReqs = ref(true)
const showShots = ref(true)

const stepRows = computed<any[]>(() => props.report?.steps || [])
const shots = computed<string[]>(() => props.report?.screenshots || [])
const shotCount = computed(() => shots.value.length)
const traffic = computed<any[]>(() => props.report?.traffic || [])

/** epoch anchor — every item is placed relative to the run's start */
const t0 = computed<number | null>(() => {
  const v = Number(props.report?.started_ts)
  return Number.isFinite(v) && v > 0 ? v : null
})

function relOf(ts: any): number | null {
  const v = Number(ts)
  if (!Number.isFinite(v) || v <= 0) return null
  return t0.value === null ? null : v - t0.value
}

/** screenshots per step, from shots_meta (+ the step's own screenshot) */
const shotsByStep = computed<Record<string, string[]>>(() => {
  const map: Record<string, string[]> = {}
  for (const m of props.report?.shots_meta || []) {
    if (!m?.path) continue
    const k = String(m.step_index ?? '')
    if (!k) continue
    ;(map[k] = map[k] || []).push(m.path)
  }
  return map
})

interface TlItem { kind: 'step' | 'req'; rel: number | null; [k: string]: any }

const timeline = computed<TlItem[]>(() => {
  const items: TlItem[] = []
  if (showSteps.value) {
    for (const st of stepRows.value) {
      items.push({
        kind: 'step',
        rel: relOf(st.started_at),
        index: st.index,
        ok: st.ok,
        title: st.action,
        detail: st.message,
        dur: st.duration_ms,
        shots: [
          ...(st.screenshot ? [st.screenshot] : []),
          ...(shotsByStep.value[String(st.index)] || []),
        ].filter((p, i, a) => a.indexOf(p) === i),
      })
    }
  }
  if (showReqs.value) {
    for (const rq of traffic.value) {
      items.push({ kind: 'req', rel: relOf(rq.ts), ...rq })
    }
  }
  items.sort((a, b) => (a.rel ?? -1) - (b.rel ?? -1))
  return items
})

function fmtRel(rel: number | null): string {
  if (rel === null || rel < 0) return '—'
  return `+${rel.toFixed(2)}s`
}

function fmtDur(ms: any): string {
  const n = Number(ms) || 0
  return n >= 1000 ? `${(n / 1000).toFixed(1)}s` : `${n}ms`
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
</script>

<style scoped>
.run-report { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.rp-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.rp-title { font-size: 12px; font-weight: 600; color: var(--app-text-primary); }
.rp-meta {
  flex: 1; font-size: 11px; color: var(--app-text-muted);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rp-ops { display: flex; gap: 4px; flex: none; }
.rp-sum { display: flex; flex-wrap: wrap; gap: 4px 10px; font-size: 11.5px; margin-bottom: 6px; }
.s-item { color: var(--app-text-secondary); }
.s-item.ok { color: #18a058; }
.s-item.bad { color: #d03050; }
.s-item.pkg { color: var(--app-text-muted); }
.crash-note { display: flex; flex-direction: column; gap: 2px; font-size: 12px; margin: 6px 0; }
.crash-text { color: #d03050; font-weight: 600; }
.crash-log { color: var(--app-text-muted); word-break: break-all; }
.rp-filters { display: flex; align-items: center; gap: 12px; margin: 8px 0 6px; font-size: 12px; }
.rp-hint { color: var(--app-text-muted); font-size: 11px; margin-left: auto; }
.tl-scroll { flex: 1; min-height: 140px; border: 1px solid var(--app-card-border); border-radius: 8px; padding: 4px 6px; }
.tl-empty { padding: 20px; text-align: center; color: var(--app-text-muted); font-size: 12px; }
.tl-row {
  display: flex; gap: 8px; align-items: flex-start;
  padding: 4px 2px; border-bottom: 1px dashed var(--app-card-border); font-size: 12px;
}
.tl-row:last-child { border-bottom: none; }
.tl-row.req { background: rgba(32, 128, 240, 0.04); }
.tl-rel {
  flex: none; width: 62px; color: var(--app-text-muted);
  font-variant-numeric: tabular-nums; font-size: 11px; padding-top: 2px;
}
.tl-kind { flex: none; max-width: 150px; }
.tl-body { flex: 1; min-width: 0; }
.tl-main {
  display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  color: var(--app-text-muted);
}
.tl-code { color: var(--app-text-muted); font-size: 11px; margin-left: 6px; }
.tl-shots { display: flex; gap: 4px; margin-top: 4px; flex-wrap: wrap; }
.rp-sec { font-size: 12px; color: var(--app-text-secondary); margin: 10px 0 6px; }
.rp-warn { color: #f0a020; font-size: 11px; margin-left: 6px; }
.shot-grid { display: flex; flex-wrap: wrap; gap: 6px; }
.req-list { max-height: 200px; overflow: auto; border: 1px solid var(--app-card-border); border-radius: 8px; padding: 4px 6px; }
.req-row { display: flex; gap: 8px; align-items: baseline; font-size: 11.5px; padding: 2px 0; }
.req-row.ok .req-s { color: #18a058; }
.req-row.warn .req-s { color: #f0a020; }
.req-row.bad .req-s { color: #d03050; }
.req-t { flex: none; width: 58px; color: var(--app-text-muted); font-variant-numeric: tabular-nums; }
.req-m { flex: none; width: 52px; font-weight: 600; color: var(--app-text-primary); }
.req-s { flex: none; width: 34px; }
.req-u { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--app-text-muted); }
</style>
