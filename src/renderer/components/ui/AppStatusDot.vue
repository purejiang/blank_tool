<template>
  <!-- 语义状态圆点。颜色与 .app-tone--* 同源（都是语义 token 当底色）。
       替代 4 套实现 / 3 种直径：StatusBar `.health-dot`(10px) 与
       DiagnosticsPage 里**同名同类**的那份、NodeConfigPanel `.npc-dot`(8px, 5 色)、
       ToolNode `.tn-status`(7px, 5 色)。 -->
  <span
    class="app-status-dot"
    :class="[`app-status-dot--${tone}`, `app-status-dot--${size}`, { 'app-status-dot--pulse': pulse }]"
    :title="title"
    role="img"
    :aria-label="title || tone"
  />
</template>

<script setup lang="ts">
export type StatusTone = 'success' | 'warning' | 'danger' | 'info' | 'primary' | 'neutral' | 'dim' | 'purple'

withDefaults(
  defineProps<{
    tone: StatusTone
    /** sm = 8px（行内标记）/ md = 10px（健康指示） */
    size?: 'sm' | 'md'
    /** 进行中/异常态呼吸动画（prefers-reduced-motion 下自动关闭，见 ui.css） */
    pulse?: boolean
    /** 悬停提示，同时用作无障碍名称 */
    title?: string
  }>(),
  { size: 'sm' },
)
</script>

<style scoped>
.app-status-dot {
  display: inline-block;
  flex: none;
  border-radius: var(--radius-pill);
}

.app-status-dot--sm { width: 8px; height: 8px; }
.app-status-dot--md { width: 10px; height: 10px; }

.app-status-dot--success { background: var(--success-text); }
.app-status-dot--warning { background: var(--warning-text); }
.app-status-dot--danger  { background: var(--danger-text); }
.app-status-dot--info    { background: var(--info-text); }
.app-status-dot--primary { background: var(--primary); }
.app-status-dot--neutral { background: var(--text-muted); }
.app-status-dot--dim     { background: var(--text-dim); }
.app-status-dot--purple  { background: var(--purple); }

.app-status-dot--pulse {
  animation: app-status-dot-pulse 1.5s var(--ease-standard) infinite;
}

@keyframes app-status-dot-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

@media (prefers-reduced-motion: reduce) {
  .app-status-dot--pulse { animation: none; }
}
</style>
