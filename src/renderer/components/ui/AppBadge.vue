<template>
  <!-- 徽章：主徽章（primary-soft + primary）/ 中性（surface-alt + text-secondary）
       / 语义四色 + 点缀紫。颜色只用 token，不用蓝色顶替成功或错误。

       这是应用里**唯一**的「标签/徽章」实现：`<n-tag>` 的软色是
       Naive 用 changeColor(semanticColor, alpha) 算出来的半透明底，与设计契约
       的实色底（.badge.ok = --success-bg）不是一回事，所以统一收编到这里。

       size：sm = 20px（契约 .badge 口径）/ xs = 16px（原 `<n-tag size="tiny">` 口径）。
       bordered：契约的 .badge 没有描边，而首页那处需要描边 —— 默认 true 保现状，
                 迁移自 `<n-tag :bordered="false">` 的站点显式传 false。 -->
  <span
    class="app-badge"
    :class="[`app-badge--${tone}`, `app-badge--${size}`, { 'app-badge--plain': !bordered }]"
  >
    <slot name="icon" />
    <slot />
  </span>
</template>

<script setup lang="ts">
export type BadgeTone =
  | 'primary'
  | 'neutral'
  | 'success'
  | 'warning'
  | 'danger'
  | 'info'
  /* 点缀紫：只用于「种类」这类标记，不参与语义四色 */
  | 'purple'

withDefaults(
  defineProps<{
    tone?: BadgeTone
    size?: 'sm' | 'xs'
    /** false = 无描边（契约 .badge 口径） */
    bordered?: boolean
  }>(),
  { tone: 'neutral', size: 'sm', bordered: true },
)
</script>

<style scoped>
.app-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-4);
  padding: 0 var(--sp-6);
  border-radius: var(--radius-chip);
  border: 1px solid transparent;
  line-height: 1;
  white-space: nowrap;
  flex: none;
}

.app-badge--sm {
  height: 20px;
  padding: 0 7px;
  font-size: var(--fs-aux);
}

.app-badge--xs {
  height: 16px;
  font-size: var(--fs-12);
}

/* 无描边：契约 .badge 只有底色，没有边 */
.app-badge--plain {
  border-color: transparent !important;
}

.app-badge--primary {
  color: var(--primary);
  background: var(--primary-soft);
  border-color: var(--primary-soft-border);
}

.app-badge--neutral {
  color: var(--text-secondary);
  background: var(--surface-alt);
  border-color: var(--border);
}

.app-badge--success {
  color: var(--success-text);
  background: var(--success-bg);
  border-color: var(--success-border);
}

.app-badge--warning {
  color: var(--warning-text);
  background: var(--warning-bg);
  border-color: var(--warning-border);
}

.app-badge--danger {
  color: var(--danger-text);
  background: var(--danger-bg);
  border-color: var(--danger-border);
}

.app-badge--info {
  color: var(--info-text);
  background: var(--info-bg);
  border-color: var(--info-border);
}

.app-badge--purple {
  color: var(--purple);
  background: var(--purple-soft);
  border-color: transparent;
}
</style>
