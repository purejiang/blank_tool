<template>
  <!-- 运行日志面板（docs/08 §3·S2 的「运行日志」）：贴画布底部的一块可折叠面板。
       数据来源两段：运行中 = stream-event 的节点/`log` 事件（`runLog.ts` 格式化）；
       终态 = `task.read_log` 读回的 per-task 日志文件（与磁盘逐字一致，含 log_path）。 -->
  <section class="run-log" data-test="run-log-panel">
    <header class="rl-hd">
      <span class="rl-title">{{ t('workflow.editor.runLog.title') }}</span>
      <span v-if="running" class="rl-state rl-state--running">
        {{ t('workflow.editor.running') }}
      </span>
      <span class="rl-count">{{ t('workflow.editor.runLog.lineCount', { count: lines.length }) }}</span>
      <span v-if="logPath" class="rl-path" :title="logPath">{{ logPath }}</span>
      <span class="rl-spacer" />
      <n-button
        size="tiny"
        quaternary
        :loading="loading"
        :title="t('workflow.editor.runLog.refresh')"
        @click="emit('refresh')"
      >
        <template #icon><AppIcon name="refresh" size="sm" /></template>
      </n-button>
      <n-button
        size="tiny"
        quaternary
        :disabled="!logPath"
        :title="t('workflow.editor.runLog.openFile')"
        @click="emit('openFile')"
      >
        <template #icon><AppIcon name="folder" size="sm" /></template>
      </n-button>
      <n-button size="tiny" quaternary :title="t('workflow.editor.dock.close')" @click="emit('close')">
        <template #icon><AppIcon name="x" size="sm" /></template>
      </n-button>
    </header>

    <div ref="bodyEl" class="rl-bd" @scroll="onScroll">
      <div v-if="lines.length === 0" class="rl-empty">
        {{ running ? t('workflow.editor.runLog.waiting') : t('workflow.editor.runLog.empty') }}
      </div>
      <div v-for="(line, index) in lines" :key="index" class="rl-line" :class="`rl-tone--${toneOf(line)}`">
        <span v-if="line.time" class="rl-time">{{ line.time }}</span>
        <span v-if="line.node" class="rl-node" :title="line.node">{{ line.node }}</span>
        <span
          v-if="line.status"
          class="rl-chip"
          :class="`rl-chip--${chipTone(line.status)}`"
        >{{ line.status }}</span>
        <span
          v-else-if="line.level && line.level !== 'info'"
          class="rl-chip"
          :class="`rl-chip--${chipTone(line.level)}`"
        >{{ line.level }}</span>
        <span class="rl-text">{{ line.text }}</span>
        <span v-if="line.error && line.error !== line.text" class="rl-text rl-err">{{ line.error }}</span>
      </div>
    </div>

    <div v-if="truncated" class="rl-note">{{ t('workflow.editor.runLog.truncated') }}</div>
  </section>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton } from 'naive-ui'

import AppIcon from '@components/ui/AppIcon.vue'
import type { RunLogLine } from './runLog'

/**
 * Presentational run-log panel. The page owns the lines (live buffer, then the
 * authoritative `task.read_log` content) and the actions; this component only
 * renders, auto-scrolls and forwards the three buttons.
 *
 * Each line renders as 「时间 | 节点 | 状态/级别 | 输出」; the tone (text color)
 * comes from the event semantics — failures red, retries/skips orange,
 * success green, plain tool output dim.
 */
const props = defineProps<{
  lines: RunLogLine[]
  /** A run is in flight — switches the empty state to 「等待输出…」. */
  running?: boolean
  loading?: boolean
  /** Per-task log file path (`task.read_log` → `log_path`); '' when unknown. */
  logPath?: string
  /** The on-disk file was longer than what we read back. */
  truncated?: boolean
}>()

const emit = defineEmits<{
  (e: 'refresh'): void
  (e: 'close'): void
  (e: 'openFile'): void
}>()

const { t } = useI18n()

type Tone = 'dim' | 'normal' | 'ok' | 'warn' | 'error'

/** Row tone from line semantics (drives the message text color). */
function toneOf(line: RunLogLine): Tone {
  if (line.kind === 'node') {
    if (line.status === 'failed') return 'error'
    if (line.status === 'skipped' || line.status === 'cancelled') return 'warn'
    return line.status ? 'normal' : 'dim'
  }
  if (line.kind === 'log') {
    const level = line.level ?? 'info'
    if (level === 'error' || level === 'critical') return 'error'
    if (level === 'warning') return 'warn'
    if (level === 'debug') return 'dim'
    return 'normal'
  }
  if (line.kind === 'workflow') {
    if (line.error) return 'error'
    if (/^success=true$/i.test(line.text)) return 'ok'
    if (/^success=false$/i.test(line.text)) return 'error'
    return 'warn'
  }
  return 'dim'
}

/** Status / level words share one chip palette (red / orange / green / muted). */
function chipTone(word: string): string {
  if (word === 'ok') return 'ok'
  if (word === 'failed' || word === 'error' || word === 'critical') return 'failed'
  if (word === 'skipped' || word === 'cancelled' || word === 'warning') return 'warn'
  return 'muted'
}

const bodyEl = ref<HTMLElement | null>(null)
/**
 * Auto-scroll only while the user is already at (or near) the bottom: a
 * console that yanks the viewport down while you are reading an earlier line
 * is worse than one that stops following. Scrolling back down re-arms it.
 */
const stickToBottom = ref(true)

function onScroll() {
  const el = bodyEl.value
  if (!el) return
  stickToBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 24
}

watch(
  () => props.lines.length,
  () => {
    if (!stickToBottom.value) return
    void nextTick(() => {
      const el = bodyEl.value
      if (el) el.scrollTop = el.scrollHeight
    })
  },
)

/** Called by the page when a new run starts (so the panel follows again). */
function resetScroll() {
  stickToBottom.value = true
  void nextTick(() => {
    const el = bodyEl.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

defineExpose({ resetScroll })
</script>

<style scoped>
/*
 * Docked inside `.canvas` (absolute, bottom edge): the canvas keeps its size and
 * the panel overlays the lower part of it while open, like a drawer. Colors and
 * type come from the app tokens so both themes work unchanged.
 */
.run-log {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 6;
  display: flex;
  flex-direction: column;
  max-height: 45%;
  background: var(--app-card-bg);
  border-top: 1px solid var(--app-card-border);
  box-shadow: 0 -6px 18px rgb(0 0 0 / 12%);
}

.rl-hd {
  display: flex;
  gap: 8px;
  align-items: center;
  flex: none;
  padding: 5px 8px 5px 10px;
  border-bottom: 1px solid var(--app-card-border);
}

.rl-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-primary);
}

.rl-state {
  padding: 0 6px;
  font-size: 11px;
  border-radius: var(--radius-chip);
}

.rl-state--running {
  color: var(--app-blue);
  background: var(--app-blue-bg);
}

.rl-count {
  font-size: 11px;
  color: var(--app-text-dim);
}

.rl-path {
  min-width: 0;
  overflow: hidden;
  font-family: var(--font-family-monospace);
  font-size: 11px;
  color: var(--app-text-dim);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rl-spacer {
  flex: 1;
}

.rl-bd {
  flex: 1;
  min-height: 60px;
  padding: 6px 10px;
  overflow-y: auto;
  font-family: var(--font-family-monospace);
  font-size: 11.5px;
  line-height: 1.7;
  overscroll-behavior: contain;
}

.rl-empty {
  font-size: 11.5px;
  color: var(--app-text-muted);
}

.rl-line {
  display: flex;
  gap: 8px;
  align-items: baseline;
  min-width: 0;
}

.rl-time {
  flex: none;
  font-variant-numeric: tabular-nums;
}

.rl-node {
  flex: none;
  max-width: 180px;
  overflow: hidden;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rl-chip {
  flex: none;
  padding: 0 6px;
  font-size: 10.5px;
  line-height: 16px;
  border-radius: var(--radius-chip);
}

.rl-chip--ok {
  color: var(--app-green);
  background: var(--app-green-bg);
}

.rl-chip--failed {
  color: var(--app-red);
  background: var(--app-red-bg);
}

.rl-chip--warn {
  color: var(--app-orange);
  background: var(--app-orange-bg);
}

.rl-chip--muted {
  color: var(--app-muted-fg);
  background: var(--app-muted-bg);
}

.rl-text {
  min-width: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

.rl-err {
  color: var(--app-red);
}

.rl-tone--normal {
  color: var(--app-text-secondary);
}

.rl-tone--dim {
  color: var(--app-text-dim);
}

.rl-tone--ok {
  color: var(--app-green);
}

.rl-tone--warn {
  color: var(--app-orange);
}

.rl-tone--error {
  color: var(--app-red);
}

.rl-note {
  flex: none;
  padding: 3px 10px;
  font-size: 11px;
  color: var(--app-orange);
  border-top: 1px solid var(--app-card-border);
}
</style>
