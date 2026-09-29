<template>
  <!-- 空态。两档：
       · size="page"（默认）— 页面级空态：虚线 art 盒 + 标题 + 说明 + 下一步动作。
         对应设计契约 ui-preview.html 的 `.empty`（`.empty .art` 是 88px 的
         1.5px 虚线盒）。替代 6 个页面各写一份的 `*-empty`（它们的虚线是 1px，
         颜色也不对，属漂移）。
       · size="inline" — 面板级占位（"暂无输入参数"这类），只有一行弱化文字。
         替代 8 处 `*-empty` / `*-placeholder` / `empty-hint` 的纯文本占位。

       空态必须给可点击的下一步（page 档）——只写「暂无数据」是半成品。 -->
  <div class="app-empty" :class="`app-empty--${size}`">
    <template v-if="size === 'page'">
      <div v-if="$slots.icon" class="app-empty-art"><slot name="icon" /></div>
      <h3 v-if="title">{{ title }}</h3>
      <p v-if="description">{{ description }}</p>
      <div v-if="$slots.actions" class="app-empty-acts"><slot name="actions" /></div>
    </template>
    <template v-else>
      <slot>{{ title }}</slot>
    </template>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    /** page = 页面级空态盒；inline = 面板内的一行占位文字 */
    size?: 'page' | 'inline'
    /** inline 档可直接用 title 传文案，也可用默认插槽 */
    title?: string
    description?: string
  }>(),
  { size: 'page' },
)
</script>

<style scoped>
.app-empty {
  min-width: 0;
  text-align: center;
}

/* ---- page：页面级 ---- */
.app-empty--page {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--sp-10);
  padding: var(--sp-40) var(--sp-20);
  color: var(--text-muted);
}

.app-empty-art {
  width: 88px;
  height: 88px;
  margin-bottom: var(--sp-4);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  background: var(--surface-alt);
  border: var(--dash-border);
  border-radius: var(--radius-card);
}

.app-empty--page h3 {
  margin: 0;
  font-size: var(--fs-14-5);
  font-weight: 600;
  color: var(--text-secondary);
}

.app-empty--page p {
  margin: 0;
  max-width: 420px;
  font-size: var(--fs-12-5);
  line-height: 1.6;
}

.app-empty-acts {
  display: flex;
  gap: var(--gap-sm);
  margin-top: var(--gap-sm);
  flex-wrap: wrap;
  justify-content: center;
}

/* ---- inline：面板级占位 ---- */
.app-empty--inline {
  padding: var(--sp-12) 0;
  font-size: var(--fs-12);
  color: var(--text-muted);
  text-align: left;
}
</style>
